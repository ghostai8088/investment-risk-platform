#!/usr/bin/env python3
"""Documentation-consistency check (placeholder, build-rule aligned).

Verifies that:
  1. Each code package/app has a README.md.
  2. The ratified governance standards carry a "Document Control" section.
  3. The closure-discipline stamp on shipped decision records.
  4. current_state.md's newest block is the one at the top, and nothing sits above it.

Exits non-zero on failure so CI blocks, preventing code/doc drift. This is a
placeholder to be extended (e.g., code-change -> required doc-change checks).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The closure-discipline teeth (API-1b OQ-W9C-5, BROADENED at the Wave-10 close OQ-W10C): a
#: record whose slice is marked DONE in the roadmap must have its Status cell stamped CLOSED — NOT
#: left at any pre-close stamp ("DRAFT for ratification" / "RATIFIED" / "pending ratification"). The
#: class recurred at SIX consecutive closes; the pre-Wave-10 teeth had TWO blind spots the sixth
#: (PPF-3) slipped through: they matched only the literal "DRAFT for ratification" (PPF-3 sat at
#: "RATIFIED"), and the done-set keyed only on the leading `✅ **DONE**` row shape (the PPF arc row
#: marks each slice INLINE as `✅ **PPF-N**`, so all three arc slices were invisible). Both are now
#: covered. Filename-keyed + row-anchored so it does NOT false-fail when a slice-id appears only in
#: another row's PROSE (the verifier's CLAIM-6 trap: "API-1b" occurs inside two `✅ **DONE**` rows),
#: nor an in-flight planning DRAFT whose own roadmap row is not yet DONE. BROADENED AGAIN at the
#: Wave-12 close: the `**Status:**` PROSE shape (CAD-1/OPS-1's record form) is recognized alongside
#: the `| **Status** |` table row — the table-only matcher had silently exempted both newest
#: records. Records with NEITHER shape (old pre-cadence records) stay out of scope.
BACKLOG_DIR = "10_delivery_backlog"
ROADMAP = "10_delivery_backlog/delivery_roadmap.md"
#: The done mark, as a PREFIX rather than a literal — the Wave-17 close's HIGH 1.
#:
#: This was the literal string ``"✅ **DONE**"`` from the gate's first version until 2026-08-11, and
#: it stopped matching anything at REF-1 (2026-07-29), when roadmap rows began writing the closure
#: date into the same bold run: ``✅ **DONE + CLOSED 2026-08-02 …**``. The consequence is the reason
#: this gate exists to be distrusted rather than trusted. With the literal unmatched, the
#: leading-title branch below never ran, so the row's actual slice id was never harvested — while
#: ``_TICK_SLICE`` happily matched ``✅ **DONE`` and added the WORD ``DONE`` to the done-set. Eleven
#: shipped slices (REF-1, CON-1, LIM-2, CAL-1, DATA-1, PERF-0, LQ-1, ONBOARD-1, ALERT-1, REPRO-2,
#: RPT-3) were therefore invisible to a CI-BLOCKING gate that had been rebuilt four times for the
#: express purpose of catching a shipped slice left at RATIFIED, and it exited 0 throughout.
#:
#: Anchored on ``DONE`` as a WORD so the mark cannot be satisfied by prose containing "done", and
#: written as a prefix so the next row shape that appends to this run does not silently re-break it.
_DONE_MARK = re.compile(r"✅\s*\*\*\s*DONE\b")
_CLOSED_MARK = "CLOSED"  # the required TERMINAL Status stamp for a shipped slice
#: A bold slice-id token: `**API-1**`, `**PPF-3**`, … (row-anchored; upper-cased to match).
_LEAD_SLICE = re.compile(r"\*\*([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)")
#: A ✅-ADJACENT bold slice token: the arc row marks each slice INLINE (`✅ **PPF-1**`), not with
#: the leading `✅ **DONE**` row shape — Wave-10's PPF arc exposed this blind spot (OQ-W10C).
_TICK_SLICE = re.compile(r"✅\s*\*\*([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)")
#: Wave-13 close: the tick INSIDE the bold — `**✅ SR-1 — … DONE …**`. SR-1 and OPS-H1 both used
#: this shape and were therefore absent from the done-set entirely, so the gate could not have
#: flagged them however they were stamped.
_BOLD_TICK_SLICE = re.compile(r"\*\*\s*✅\s*([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)")


def _done_slice_ids(roadmap_text: str) -> set[str]:
    """The slice-ids marked done in the roadmap. Two shapes are recognized (the Wave-10 broadening,
    OQ-W10C): a normal row's leading bold title on a ``✅ **DONE**`` line, AND every ✅-adjacent
    bold token on any ``DONE`` line (the arc row's inline ``✅ **PPF-1**`` shape). Extra non-slice
    tokens (DONE/ALL) never match a decision-record filename, so they cannot false-flag."""
    done: set[str] = set()
    for line in roadmap_text.splitlines():
        if "✅" not in line or "DONE" not in line.upper():
            continue
        if _DONE_MARK.search(line):  # a normal `… **SLICE …** ✅ **DONE …** …` row → leading token
            m = _LEAD_SLICE.search(line)
            if m:
                done.add(m.group(1).upper())
        for m in _TICK_SLICE.finditer(line):  # arc-style inline `✅ **SLICE**` marks
            done.add(m.group(1).upper())
        # Wave-13 close fold: the tick INSIDE the bold — `**✅ SR-1 — … DONE + CLOSED …**`. Both
        # SR-1 and OPS-H1 wrote their roadmap rows this way, so neither slice was in the done-set
        # at all and neither could ever be flagged. `_TICK_SLICE` requires `✅` followed by `**`,
        # which is exactly inverted for this shape.
        for m in _BOLD_TICK_SLICE.finditer(line):
            done.add(m.group(1).upper())
    return done


#: Wave-13 close: the Status key with ANY emphasis — `| Status |`, `| **Status** |`, `| *Status* |`
#: — plus the prose `**Status:**` / `Status:` forms. Anchored, so prose merely QUOTING a Status line
#: is still not mistaken for one (the API-1b OD-API-1b-E case the anchoring was added for).
_STATUS_ROW = re.compile(r"^\|\s*\*{0,2}_?\s*Status\s*_?\*{0,2}\s*\|", re.IGNORECASE)
_STATUS_PROSE = re.compile(r"^\*{0,2}Status\*{0,2}\s*:", re.IGNORECASE)


def _status_lines(record_text: str) -> list[str]:
    """The record's actual Status line(s).

    **Wave-13 close fold — this matcher was the reason the gate saw NOTHING.** It recognized only
    the BOLDED table key ``| **Status** |`` and the prose ``**Status:**``. Every Wave-13 record
    writes the key UNBOLDED (``| Status |``), so ``_status_lines`` returned an empty list for all
    five, ``_is_unstamped_shipped`` short-circuited on ``not status_lines``, and the gate reported
    clean while FE-M1 actually shipped with its Status cell reading ``RATIFIED … Implementation
    next``. Measured at the close: 20 roadmap-DONE records were invisible to the gate this way.

    That is the SEVENTH recurrence of the closure-discipline class and the THIRD time the fix has
    been "broaden the matcher" (OQ-W9C-5 → OQ-W10C → Wave-12 close → here). Broadening alone has
    now failed three times because each broadening is only as good as the shapes someone thought to
    enumerate, so this fold also adds a NON-VACUITY FLOOR (see ``_closure_stamp_errors``): if the
    gate's in-scope population ever collapses again, the floor fails loudly instead of the gate
    silently guarding nothing.

    Each pattern is ANCHORED — prose that quotes or describes a Status line (as API-1b's own
    OD-API-1b-E does) must still not be mistaken for one.
    """
    return [
        ln
        for ln in record_text.splitlines()
        if _STATUS_ROW.match(ln.strip()) or _STATUS_PROSE.match(ln.strip())
    ]


def _is_unstamped_shipped(slice_id: str, status_lines: list[str], done: set[str]) -> bool:
    """The rule's TEETH (pure, unit-tested): a record is an unstamped-shipped miss iff its slice is
    DONE in the roadmap AND it HAS a Status cell NOT yet stamped CLOSED — catching a record stuck at
    ANY pre-close stamp (``DRAFT for ratification`` / ``RATIFIED`` / ``pending ratification``), not
    just the one literal the pre-Wave-10 gate matched (OQ-W10C: the class recurred a 6th time —
    PPF-3 sat at "RATIFIED", past the old teeth). Records with no Status cell stay out of scope."""
    if slice_id not in done or not status_lines:
        return False
    return not any(_CLOSED_MARK in ln for ln in status_lines)


#: Wave-13 close — the NON-VACUITY FLOORS. Measured at the fold: 61 records carry a recognized
#: Status line and 45 slice-ids are in the roadmap done-set. The floors sit deliberately BELOW the
#: measured values (records are only ever added) and exist to fail LOUDLY if a future shape drift
#: silently shrinks the gate's population again — which is exactly how this control reported clean
#: while guarding nothing for an entire wave. `test_ci_pg_coverage.py` uses the same pattern.
#:
#: The lesson these encode: three consecutive fixes to this gate were "broaden the matcher", and a
#: matcher is only as good as the shapes someone thought to enumerate. A floor does not need to
#: anticipate the next shape — it only needs to notice that coverage fell.
_MIN_RECORDS_WITH_STATUS = 50
_MIN_DONE_SLICES = 38
#: **Named witnesses, one group per parser branch (Wave-17 close, HIGH 1).** A count floor is the
#: wrong instrument here and its failure is on the record: the done-set kept 55 members while
#: silently losing every slice shipped after 2026-07-29, and 55 > 38, so the floor stayed quiet.
#: Say what must be IN the set.
#:
#: * ``REF-1``/``DATA-1``/``LQ-1`` — the ``✅ **DONE + CLOSED …**`` rows, the shape that broke.
#: * ``PPF-1``/``PPF-3`` — the Wave-10 arc's inline ``✅ **PPF-1**`` marks (``_TICK_SLICE``).
#: * ``SR-1``/``OPS-H1`` — the Wave-13 tick-inside-the-bold shape (``_BOLD_TICK_SLICE``).
#: * ``API-1`` — the plain early shape, so the original branch keeps a witness too.
_MUST_PARSE_AS_DONE = frozenset(
    {"REF-1", "DATA-1", "LQ-1", "PPF-1", "PPF-3", "SR-1", "OPS-H1", "API-1"}
)

#: Decision records whose Status line the matcher does NOT recognize, enumerated EXACTLY.
#:
#: Added at REF-1 after the closure-stamp class recurred an EIGHTH time — in the REF-1 planning
#: record itself, whose status sat inside a blockquote so neither ``_STATUS_ROW`` nor
#: ``_STATUS_PROSE`` anchored after stripping. The two count floors above could never have caught
#: it: 61 of 62 records still had a recognized status, comfortably above the floor of 50. A MINIMUM
#: is blind to one record going dark; only an EXACT set is not.
#:
#: This is a grandfather list, not an allowlist to grow. A NEW record that the matcher cannot see
#: fails the gate by name. Removing entries (by giving those records a recognized Status line) is
#: always welcome; adding one requires explaining why a record may be invisible to the gate that
#: exists to read it.
_RECORDS_WITHOUT_RECOGNIZED_STATUS: frozenset[str] = frozenset(
    {
        "bt_1_decision_record.md",
        "md_h1_decision_record.md",
        "p3_6_decision_record.md",
        "pa_0_decision_record.md",
        "pa_1_decision_record.md",
        "pa_2_decision_record.md",
        "pa_3_decision_record.md",
        "pa_4_decision_record.md",
        "rd_1_decision_record.md",
        "rd_2_decision_record.md",
        "rd_3_decision_record.md",
    }
)


def _closure_stamp_errors() -> list[str]:
    roadmap_path = ROOT / ROADMAP
    if not roadmap_path.is_file():
        return [f"missing roadmap: {ROADMAP}"]
    done = _done_slice_ids(roadmap_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    with_status = 0
    for record in sorted((ROOT / BACKLOG_DIR).glob("*_decision_record.md")):
        slice_id = record.name.removesuffix("_decision_record.md").replace("_", "-").upper()
        status_lines = _status_lines(record.read_text(encoding="utf-8"))
        if status_lines:
            with_status += 1
        elif record.name not in _RECORDS_WITHOUT_RECOGNIZED_STATUS:
            errors.append(
                f"{record.name}: no Status line the closure-stamp gate can SEE. The gate "
                f"short-circuits on records it cannot read, so this record would ship unstamped "
                f"with the gate green (the eighth recurrence of that class, found at REF-1). "
                f"Use a `| Status | ... |` table row or an unprefixed `**Status:** ...` line — a "
                f"blockquote-prefixed status does not anchor."
            )
        if _is_unstamped_shipped(slice_id, status_lines, done):
            errors.append(
                f"{record.name}: slice {slice_id} is DONE in the roadmap but its Status cell is "
                f"not stamped CLOSED (the OQ-W9C-5 / OQ-W10C closure-discipline rule)"
            )
    # The Wave-17 close's replacement for a count floor, and the reason it is named rather than
    # counted: this gate's done-set fell from "every shipped slice" to "every shipped slice before
    # 2026-07-29 plus the literal word DONE" and the count barely moved — 55 parsed against a floor
    # of 38. A quantity floor cannot see a set that stays large while losing the members that
    # matter. Each witness below is a slice that has SHIPPED and can never un-ship, and the three
    # groups are the three parser branches, so a regression in any one of them names itself.
    missing_witnesses = sorted(_MUST_PARSE_AS_DONE - done)
    if missing_witnesses:
        errors.append(
            f"closure-stamp gate NON-VACUITY: the roadmap's done-set no longer contains "
            f"{', '.join(missing_witnesses)} — slices that have SHIPPED and cannot un-ship. The "
            f"row-shape parser has lost a branch (see _DONE_MARK / _TICK_SLICE / "
            f"_BOLD_TICK_SLICE). Fix the parser; do NOT remove the witness."
        )
    if with_status < _MIN_RECORDS_WITH_STATUS:
        errors.append(
            f"closure-stamp gate NON-VACUITY: only {with_status} decision records have a "
            f"recognized Status line (floor {_MIN_RECORDS_WITH_STATUS}). The gate's matcher has "
            f"lost coverage — fix _status_lines rather than lowering this floor."
        )
    if len(done) < _MIN_DONE_SLICES:
        errors.append(
            f"closure-stamp gate NON-VACUITY: only {len(done)} slice-ids parsed from the roadmap "
            f"done-set (floor {_MIN_DONE_SLICES}). Fix _done_slice_ids rather than the floor."
        )
    return errors


# ---------------------------------------------------------------------------------------------
# current_state.md freshness (housekeeping fold, 2026-08-14)
# ---------------------------------------------------------------------------------------------
#
# CLAUDE.md orders every session to read `current_state.md` SECOND, before doing anything. On
# 2026-08-14 the first thing that file said was:
#
#     ## ⚠️ CURRENT TRUTH (2026-08-08, latest) — read this block; everything below it is HISTORY
#
# Its `NEXT` named the ONBOARD-1a implementation plan, which had shipped as PR #191 twenty-three
# merges earlier. The real current truth was a hundred lines further down, underneath a heading
# instructing the reader to treat it as history.
#
# This is the SECOND recurrence, and the first is written up two blocks below in the same file: the
# Wave-17 close found that "P1 ledger (4) went unswept across five consecutive slice closeouts" and
# that `test_ledger_census.py:19` deliberately leaves that ledger PROCEDURAL, so nothing mechanical
# would ever catch it. The fix applied at that close was to append a newer block UNDERNEATH the
# stale one, which is precisely how the class recurred the same week.
#
# So this is the P7 shape rather than a promise to sweep harder: a block that is not the newest
# block fails `make check`.
#
# SCOPE, and what was deliberately REMOVED after adversarial review (2026-08-14, four lanes):
#
#   * The first version of this gate also asserted that a migration head named in the top block
#     equalled the head derived from `migrations/versions/`. It is GONE. Measured at review: that
#     rule would have reddened CI on 19 of the last 21 migration commits, because CI runs `on:
#     push` and the head changes in a commit that has no reason to touch this document. Worse, it
#     re-minted a head literal that a RATIFIED process fold of 2026-08-09 had deliberately
#     consolidated into one line — `test_migration_head.py` says in as many words, "a new migration
#     edits exactly this line, and nothing else" — after 21 hand-mirrored copies caused "22 stale
#     pins in one fold" at the Wave-16 close. And it bought nothing here: on the 2026-08-14 defect
#     the ordering rules below fire independently, so the stale head was a symptom, not a second
#     finding. The closeout sweep (claude_operating_instructions.md, ledger 4) owns head freshness.
#
#   * Deliberately NOT checked: whether the prose is TRUE. Unautomatable for the same reason G2 is
#     (see scripts/check_g2_adjudication.py) — every word-based rule is one rewording away from
#     being switched off by the person it polices. What IS checked is the document's STRUCTURE,
#     which a machine can read exactly.
#
#   * Also NOT checked, and named so nobody mistakes silence for coverage: whether a new block was
#     written AT ALL. A file that simply stopped being updated is perfectly ordered and passes.
#     That is the likelier recurrence, and closing it needs an anchor outside the document; the
#     candidate (the newest CC-Session-Logs filename date) was declined at the review gate because
#     it ties a repository gate to a personal workflow artifact. Staleness-by-omission remains
#     procedural.
CURRENT_STATE = "docs/project_memory/current_state.md"

#: A dated "truth" heading, at any heading level, optionally inside a blockquote. Three spellings
#: are in use in the file today. `kind` is CAPTURED so the classification below can use it rather
#: than re-scanning the raw line: an author writing "Prior current truth" without the hyphen must
#: not read as a second CURRENT TRUTH heading, and a substring test on the raw line does exactly
#: that (adversarial review, false-positive lane).
#: `Prior current[- ]truth` accepts EITHER spelling, and the character class is the load-bearing
#: part. With `Prior current-truth` (hyphen only), the lazy `.*?` walks past "Prior " — where no
#: alternative matches — and then matches "CURRENT TRUTH" inside "Prior current truth", so a
#: DEMOTED block reads as a second current one and the author is told to demote a heading that is
#: already demoted. The alternation ORDER is irrelevant here and was measured to be so: with a
#: lazy quantifier the earliest matching POSITION wins regardless of which alternative is listed
#: first, so reordering is an equivalent mutant. Widening the class is what fixes it.
_TRUTH_HEADING = re.compile(
    r"^>?\s*#{1,6}\s+.*?(?P<kind>Prior current[- ]truth|Previous truth|CURRENT TRUTH)",
    re.IGNORECASE,
)
#: Any ATX heading, quoted or not — used only to measure how much of the file this gate can SEE.
_ANY_HEADING = re.compile(r"^>?\s*#{1,6}\s+\S")
#: The document TITLE: a single unquoted `#`. Exactly one of these may precede the first truth
#: heading, and nothing else may. Allowing "any H1" instead would reopen the hole this rule exists
#: to close, because `# ⚠️ READ THIS FIRST` is an H1 too — so the allowance is positional (the very
#: first heading in the file) rather than a property of the text.
_H1_TITLE = re.compile(r"^#\s+\S")
#: An ISO date, tolerating the disambiguating letter this file appends when a day carries more than
#: one block (`2026-07-29c`). A trailing `\b` does NOT match a digit followed by a letter, and the
#: first run of this gate failed on exactly that heading. The lookahead still rejects a longer
#: digit run or a further date part.
_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})(?![\d-])")
#: A fenced code block. Stripped before anything is scanned, because this file's house style is to
#: QUOTE the stale heading it is fixing — the gate's own docstring does it — and a quoted heading
#: is a citation, not a block. Left in, it reads as a duplicate CURRENT TRUTH and, worse, as an
#: out-of-order block (adversarial review, false-positive lane).
_FENCE = re.compile(r"^\s*(?:```|~~~)")

#: Non-vacuity floor. Nine dated truth headings exist today. The floor is deliberately LOW because
#: the quantity it guards is one this project has already ratified SHRINKING once: pre-2026-07-29b
#: blocks were moved to `current_state_archive.md` on 2026-07-30, a user-ratified document-surface
#: shrink, and the same act is on the table again. Two is the invariant that actually matters —
#: a current block, and something below it to be newer than. Shape drift is caught by the coverage
#: ratio below instead, which does not punish archiving.
_MIN_TRUTH_HEADINGS = 2
#: At least this share of the file's headings must be truth headings the matcher RECOGNISES. Today
#: the file is 9 truth headings out of 16 total (0.56). This replaces a count floor, which cannot
#: tell "blocks were archived" (legitimate) from "the heading shape drifted past the matcher"
#: (the failure). The closure-discipline gate above guarded NOTHING for an entire wave while
#: exiting 0, for exactly the want of a check like this.
_MIN_TRUTH_HEADING_SHARE = 0.30


def _strip_fences(text: str) -> str:
    """Blank out fenced code blocks, preserving line numbering."""
    out, in_fence = [], False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def _truth_headings(text: str) -> list[tuple[str, str, str | None]]:
    """Every dated truth heading, in file order, as (heading, kind, its own date).

    The date is the FIRST ISO date on the line, not the maximum. `max()` was the first version and
    it is an escape hatch: appending "re-confirmed 2026-08-14" to a stale 2026-08-08 heading — six
    characters — sorts that heading to the top and silences the ordering check entirely
    (adversarial review, false-negative lane F3). It also mis-sorts the file's own legitimate
    cross-reference style, "Previous truth (2026-08-08) — superseded at the 2026-08-12 re-baseline".
    Every heading in the file today writes its OWN date first, so first-wins is both safer and
    truer to the house style. A span (`2026-08-12/13`) yields its opening date, which is correct
    for ordering.
    """
    out: list[tuple[str, str, str | None]] = []
    for line in _strip_fences(text).splitlines():
        m = _TRUTH_HEADING.match(line)
        if not m:
            continue
        dates = _ISO_DATE.findall(line)
        raw = m.group("kind").upper()
        # Canonicalise so the hyphen is not load-bearing for callers either.
        kind = "PRIOR CURRENT-TRUTH" if raw.startswith("PRIOR") else raw
        out.append((line.strip(), kind, dates[0] if dates else None))
    return out


def _freshness_errors(text: str) -> list[str]:
    """The rule's teeth, pure and unit-tested."""
    errors: list[str] = []
    stripped = _strip_fences(text)
    headings = _truth_headings(text)
    all_headings = [ln for ln in stripped.splitlines() if _ANY_HEADING.match(ln)]

    if len(headings) < _MIN_TRUTH_HEADINGS:
        return [
            f"current_state.md freshness NON-VACUITY: only {len(headings)} dated truth headings "
            f"parsed (floor {_MIN_TRUTH_HEADINGS}). Either the heading shape has drifted past "
            f"_TRUTH_HEADING, or the file has been archived down past the point where 'newest "
            f"first' means anything. If the shape drifted, fix the matcher. If blocks were "
            f"archived, this gate has nothing left to order and should be reconsidered."
        ]

    share = len(headings) / len(all_headings) if all_headings else 0.0
    if share < _MIN_TRUTH_HEADING_SHARE:
        errors.append(
            f"current_state.md freshness NON-VACUITY: only {len(headings)} of "
            f"{len(all_headings)} headings are truth headings this gate recognises "
            f"({share:.0%}, floor {_MIN_TRUTH_HEADING_SHARE:.0%}). The heading shape has drifted "
            f"past _TRUTH_HEADING and the gate is ordering a shrinking minority of the file. Fix "
            f"the matcher, not the floor."
        )

    undated = [h for h, _, d in headings if d is None]
    if undated:
        errors.append(
            "current_state.md: these truth headings carry no ISO date, so they cannot be ordered "
            "and the block above them cannot be proven newest: " + "; ".join(undated)
        )

    # (1) STRUCTURAL. The first heading in the file after the title must be the current block.
    #     Without this, a stale "read this first" banner written as `#`, `#####`, bold, or any
    #     wording the matcher does not know sits ABOVE everything and is invisible to every other
    #     check — the 2026-08-14 defect verbatim, reinstated, passing (review, lane F1).
    allowance = 1 if all_headings and _H1_TITLE.match(all_headings[0]) else 0
    first_truth = next((i for i, ln in enumerate(all_headings) if _TRUTH_HEADING.match(ln)), None)
    if first_truth is not None and first_truth > allowance:
        errors.append(
            f"current_state.md: {all_headings[allowance].strip()!r} sits above the first truth "
            f"block. Only the document title may precede it. A reader following CLAUDE.md acts on "
            f"the first thing they meet, so a banner here is read as current whatever it is called."
        )

    # (2) Exactly one block claims to be current, classified off the CAPTURED kind.
    current = [h for h, k, _ in headings if k == "CURRENT TRUTH"]
    if not current:
        errors.append(
            "current_state.md: no `CURRENT TRUTH` heading. The file every session is ordered to "
            "read second must say which block is true now."
        )
    elif len(current) > 1:
        errors.append(
            f"current_state.md: {len(current)} headings claim CURRENT TRUTH. Exactly one block is "
            f"true now; demote the rest to `Previous truth`. Headings: " + " | ".join(current)
        )
    elif headings[0][1] != "CURRENT TRUTH":
        errors.append(
            f"current_state.md: the CURRENT TRUTH block is not the first truth block. The topmost "
            f"is {headings[0][0]!r}. A reader reads this file top-down and acts on what they meet "
            f"first."
        )

    # (3) Dates never increase as you read down. THE check that would have fired on 2026-08-14:
    #     a 08-12/13 block and a 08-11 block both sat BELOW a block labelled "(2026-08-08, latest)".
    #     Walked over every adjacent pair, not just the first — truncating the walk to the top pair
    #     survived the first version's whole test suite (review, vacuity lane).
    dated = [(h, d) for h, _, d in headings if d is not None]
    for (h_above, d_above), (h_below, d_below) in zip(dated, dated[1:], strict=False):
        if d_below > d_above:
            errors.append(
                f"current_state.md: a NEWER block sits below an OLDER one. {h_below!r} "
                f"({d_below}) is below {h_above!r} ({d_above}). Newest first — a stale block at "
                f"the top is read as current and acted on."
            )
    return errors


def _current_state_errors(root: Path | None = None) -> list[str]:
    """Read the real file and apply the rules.

    ``root`` is injectable ONLY so a test can run the whole path — including `main()` — against a
    fabricated tree. The first version had no such seam, and the consequence was measured: deleting
    the `main()` call to this function left all twenty of its tests green while `check_docs.py`
    printed "Documentation check passed" over the 2026-08-14 defect (review, vacuity lane).
    """
    path = (root or ROOT) / CURRENT_STATE
    if not path.is_file():
        return [f"missing entry-point snapshot: {CURRENT_STATE}"]
    return _freshness_errors(path.read_text(encoding="utf-8"))


PACKAGE_DIRS = [
    "apps/backend",
    "apps/frontend",
    "apps/worker",
    "packages/shared-python",
    "packages/shared-ts",
]

STANDARDS_REQUIRING_DOC_CONTROL = [
    "00_ai_operating_model/reconciled_agent_role_registry.md",
    "01_product_strategy/regulatory_product_scope.md",
    "03_architecture/architecture_baseline.md",
    "03_architecture/foundational_adrs.md",
    "03_architecture/foundation_slice.md",
    "04_data_model/canonical_data_model_standard.md",
    "04_data_model/temporal_reproducibility_standard.md",
    "04_data_model/audit_event_taxonomy.md",
    "05_analytics_methodologies/numerical_quant_standards.md",
    "06_security/entitlement_sod_model.md",
    "06_security/threat_model_initial.md",
    "07_model_governance/model_governance_independence_policy.md",
    "08_testing_qa/ci_enforcement_overview.md",
    "09_compliance_controls/control_matrix_skeleton.md",
]


def main() -> int:
    errors: list[str] = []

    for pkg in PACKAGE_DIRS:
        if not (ROOT / pkg / "README.md").is_file():
            errors.append(f"missing README.md in {pkg}")

    for doc in STANDARDS_REQUIRING_DOC_CONTROL:
        path = ROOT / doc
        if not path.is_file():
            errors.append(f"missing governance doc: {doc}")
        elif "Document Control" not in path.read_text(encoding="utf-8"):
            errors.append(f"missing Document Control header: {doc}")

    errors.extend(_closure_stamp_errors())
    errors.extend(_current_state_errors())

    if errors:
        print("Documentation check FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("Documentation check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
