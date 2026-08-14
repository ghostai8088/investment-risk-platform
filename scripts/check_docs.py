#!/usr/bin/env python3
"""Documentation-consistency check (placeholder, build-rule aligned).

Verifies that:
  1. Each code package/app has a README.md.
  2. The ratified governance standards carry a "Document Control" section.
  3. The closure-discipline stamp on shipped decision records.
  4. current_state.md's newest block is the one at the top, and its migration head is real.

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
# Two load-bearing facts in that block were wrong. Its `NEXT` named the ONBOARD-1a implementation
# plan, which had shipped as PR #191 twenty-three merges earlier; and it stated migration head
# `0068_entitlement_request` when the head on disk was `0070_app_role`. The real current truth was
# a hundred lines further down, underneath a heading instructing the reader to treat it as history.
#
# This is the SECOND recurrence, and the first one is written up two blocks below in the same file:
# the Wave-17 close found that "P1 ledger (4) went unswept across five consecutive slice closeouts"
# and that `test_ledger_census.py:19` deliberately leaves that ledger PROCEDURAL, so nothing
# mechanical would ever catch it. The fix applied at that close was to append a newer block
# UNDERNEATH the stale one, which is precisely how the class recurred the same week.
#
# So this is the P7 shape rather than a promise to sweep harder: a new block that is not the newest
# block, or a migration head the repository does not have, fails `make check`.
#
# Deliberately NOT checked: whether the prose is true. That is unautomatable for the same reason G2
# is (see scripts/check_g2_adjudication.py) — any word-based rule is one rewording away from being
# switched off by the person it polices. These two facts are checked because both are machine-
# comparable against something outside the document.
CURRENT_STATE = "docs/project_memory/current_state.md"

#: A dated "truth" heading, at any heading level, optionally inside a blockquote. Three spellings
#: are in use in the file today: `CURRENT TRUTH`, `Previous truth` and `Prior current-truth`.
_TRUTH_HEADING = re.compile(
    r"^>?\s*#{2,4}\s+.*?(?P<kind>CURRENT TRUTH|Previous truth|Prior current-truth)",
    re.IGNORECASE,
)
#: An ISO date, tolerating the disambiguating letter this file appends when a day has more than one
#: block (`2026-07-29c`). A trailing `\b` would NOT match that, and the first run of this gate
#: failed on exactly it. The lookahead still rejects a longer digit run or a further date part.
_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})(?![\d-])")
#: `Migration head \`0070_app_role\``, with or without emphasis between the words and the tick.
_HEAD_CLAIM = re.compile(r"[Mm]igration head[^\n`]{0,60}`(?P<rev>\d{4}_[a-z0-9_]+)`")

#: Non-vacuity floor. The file carries nine dated truth headings today. A parser that stops
#: recognising the heading shape would otherwise leave this gate ordering an empty list and exiting
#: 0 — which is exactly how the closure-discipline gate above guarded nothing for an entire wave.
_MIN_TRUTH_HEADINGS = 5


def _truth_headings(text: str) -> list[tuple[str, str | None]]:
    """Every dated truth heading, in file order, as (heading, newest ISO date in it).

    The date is the MAXIMUM of the dates in the heading, because a block may span days — the
    re-baseline heading read `2026-08-12/13`, and the Wave-17 close heading carries its date at the
    end of the line rather than in parentheses.
    """
    out: list[tuple[str, str | None]] = []
    for line in text.splitlines():
        if not _TRUTH_HEADING.match(line):
            continue
        dates = _ISO_DATE.findall(line)
        out.append((line.strip(), max(dates) if dates else None))
    return out


def _top_block(text: str) -> str:
    """The text from the first truth heading up to the second one."""
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines) if _TRUTH_HEADING.match(ln)]
    if not starts:
        return ""
    end = starts[1] if len(starts) > 1 else len(lines)
    return "\n".join(lines[starts[0] : end])


def _freshness_errors(text: str, actual_head: str) -> list[str]:
    """The rule's teeth, pure and unit-tested.

    ``actual_head`` is the migration head derived from the repository, never from the document.
    """
    errors: list[str] = []
    headings = _truth_headings(text)

    if len(headings) < _MIN_TRUTH_HEADINGS:
        errors.append(
            f"current_state.md freshness NON-VACUITY: only {len(headings)} dated truth headings "
            f"parsed (floor {_MIN_TRUTH_HEADINGS}). The heading shape has drifted past "
            f"_TRUTH_HEADING, so this gate is ordering almost nothing. Fix the matcher, not the "
            f"floor."
        )
        return errors

    undated = [h for h, d in headings if d is None]
    if undated:
        errors.append(
            "current_state.md: these truth headings carry no ISO date, so they cannot be ordered "
            "and the block above them cannot be proven newest: " + "; ".join(undated)
        )
        return errors

    # (1) The top block must be the CURRENT one, and the only CURRENT one.
    current = [h for h, _ in headings if "CURRENT TRUTH" in h.upper()]
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
    elif "CURRENT TRUTH" not in headings[0][0].upper():
        errors.append(
            f"current_state.md: the CURRENT TRUTH block is not at the top of the file. The topmost "
            f"heading is {headings[0][0]!r}. A reader following CLAUDE.md reads this file top-down "
            f"and acts on the first block they meet."
        )

    # (2) Dates must never increase as you read down. This is the check that would have fired on
    #     2026-08-14: a 08-12/13 block and a 08-11 block both sat BELOW a block labelled
    #     "(2026-08-08, latest)".
    # `strict=False` is deliberate: the two sequences differ in length by one BY CONSTRUCTION —
    # this is the adjacent-pairs walk, and the last heading has nothing below it to compare against.
    for (h_above, d_above), (h_below, d_below) in zip(headings, headings[1:], strict=False):
        if d_below > d_above:  # type: ignore[operator]
            errors.append(
                f"current_state.md: a NEWER block sits below an OLDER one. {h_below!r} "
                f"({d_below}) is below {h_above!r} ({d_above}). Newest first — a stale block at "
                f"the top is read as current and acted on."
            )

    # (3) Any migration head the top block claims must be the head the repository actually has.
    top = _top_block(text)
    claimed = _HEAD_CLAIM.findall(top)
    if not claimed:
        errors.append(
            "current_state.md: the CURRENT TRUTH block names no migration head, so half this gate "
            "is guarding nothing. State it as: Migration head `<revision>`."
        )
    for rev in claimed:
        if rev != actual_head:
            errors.append(
                f"current_state.md: the CURRENT TRUTH block claims migration head `{rev}`, but "
                f"the repository's head is `{actual_head}`. This exact drift shipped on "
                f"2026-08-14 (claimed 0068, actual 0070)."
            )
    return errors


def _actual_migration_head() -> str:
    """The head, from alembic itself — the same source `test_migration_head.py` pins against.

    Deliberately not read from any document: a check that compares one piece of prose against
    another proves only that someone copied it twice (the CON-1 lesson — ask the database).
    """
    from alembic.script import ScriptDirectory

    return ScriptDirectory(str(ROOT / "migrations")).get_current_head() or ""


def _current_state_errors() -> list[str]:
    path = ROOT / CURRENT_STATE
    if not path.is_file():
        return [f"missing entry-point snapshot: {CURRENT_STATE}"]
    return _freshness_errors(path.read_text(encoding="utf-8"), _actual_migration_head())


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
